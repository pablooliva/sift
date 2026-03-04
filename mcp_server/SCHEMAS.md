# MCP Tool Response Schemas

**Version:** 1.3
**Last Updated:** 2026-02-13
**Related Specs:** SPEC-037 (MCP Graphiti Integration), SPEC-041 (Temporal Data)

## Overview

This document defines the response schemas for all txtai MCP (Model Context Protocol) tools. These schemas describe the exact JSON structure returned by each tool, including optional knowledge graph enrichment fields.

**Purpose:**
- Provide formal API reference for tool consumers (Claude Code, other MCP clients)
- Document enriched response formats (knowledge graph integration)
- Enable reliable response parsing and testing

**When to use this document:**
- Building MCP client integrations
- Writing tests that assert on response structure
- Understanding knowledge graph enrichment behavior
- Debugging unexpected response formats

## Common Response Pattern

All tools follow a consistent base structure:

```json
{
  "success": true,        // boolean - whether operation succeeded
  "error": null,          // string|null - error message if failed
  "response_time": 0.5    // number - operation duration in seconds (optional)
}
```

**Error responses:**
```json
{
  "success": false,
  "error": "Descriptive error message"
}
```

Tool-specific fields are added to this base structure.

---

## Tool Schemas

### 1. rag_query - RAG Answers with Knowledge Graph

Generate answers to questions using RAG (Retrieval-Augmented Generation) with optional knowledge graph enrichment.

#### Standard Response

**Parameters:**
- `question` (string) - User question
- `include_graph_context` (boolean, default: false) - Enable knowledge graph enrichment

**Response schema (include_graph_context=false):**

```json
{
  "success": true,
  "answer": "The generated answer text based on retrieved documents...",
  "sources": [
    {
      "id": "uuid-1",
      "title": "Document Title",
      "score": 0.85
    }
  ],
  "response_time": 7.2
}
```

**Field descriptions:**
- `success` (boolean) - Always true for successful RAG queries
- `answer` (string) - LLM-generated answer based on retrieved context
- `sources` (array) - List of source documents used for answer generation
  - `id` (string) - Document UUID
  - `title` (string) - Document title or filename
  - `score` (number) - Relevance score (0.0-1.0)
- `response_time` (number) - Total query time in seconds

**Error response:**
```json
{
  "success": false,
  "error": "Together AI API error: Rate limit exceeded"
}
```

#### Enriched Response (Knowledge Graph)

**Response schema (include_graph_context=true):**

```json
{
  "success": true,
  "answer": "The generated answer text...",
  "sources": [
    {
      "id": "uuid-1",
      "title": "Document Title",
      "score": 0.85,
      "graphiti_context": {
        "entities": [
          {"name": "TechCorp", "type": "Organization"},
          {"name": "Alice Smith", "type": "Person"}
        ],
        "relationships": [
          {
            "source": "Alice Smith",
            "target": "TechCorp",
            "type": "WORKS_AT"
          }
        ]
      }
    }
  ],
  "graphiti_status": "available",
  "knowledge_context": {
    "entities": [
      {"name": "TechCorp", "type": "Organization"},
      {"name": "Alice Smith", "type": "Person"}
    ],
    "relationships": [
      {
        "source": "Alice Smith",
        "target": "TechCorp",
        "type": "WORKS_AT"
      }
    ],
    "entity_count": 2,
    "relationship_count": 1
  },
  "response_time": 8.5
}
```

**Additional enriched fields:**
- `graphiti_status` (string) - Knowledge graph enrichment status (see [Appendix: graphiti_status](#graphiti_status-values))
- `knowledge_context` (object|null) - Aggregated entities/relationships from all sources
  - `entities` (array) - Unique entities from all source documents
    - `name` (string) - Entity name
    - `type` (string) - Entity type (Person, Organization, Concept, etc.)
  - `relationships` (array) - All relationships between entities
    - `source` (string) - Source entity name
    - `target` (string) - Target entity name
    - `type` (string) - Relationship type (WORKS_AT, RELATES_TO, etc.)
  - `entity_count` (number) - Total unique entities
  - `relationship_count` (number) - Total relationships
- `sources[].graphiti_context` (object|null) - Per-document knowledge graph context
  - Same structure as `knowledge_context` but scoped to single document

**Temporal context in RAG (SPEC-041):**

When `include_graph_context=true`, knowledge graph relationships are included in the LLM prompt with temporal metadata:

**Format:** `(added: YYYY-MM-DD[, valid: YYYY-MM-DD])`

**Example prompt snippet:**
```
Knowledge graph context:
- Python USED_FOR Machine Learning (added: 2026-02-13)
- TensorFlow ENABLES Deep Learning (added: 2026-02-10, valid: 2025-12-01)
```

**Temporal annotation rules:**
- `created_at` always appears first as "added: YYYY-MM-DD"
- `valid_at` appears as "valid: YYYY-MM-DD" if present and non-null
- Date-only format (YYYY-MM-DD) used for readability (time component stripped)
- Enables time-aware LLM responses (e.g., "As of February 2026, Python was used for ML...")

**Note:** Temporal context is automatically included when enrichment is enabled. No additional parameters required.

**Enrichment status examples:**

**Status: "available"** (successful enrichment)
```json
{
  "graphiti_status": "available",
  "knowledge_context": {
    "entities": [...],
    "relationships": [...],
    "entity_count": 5,
    "relationship_count": 3
  }
}
```

**Status: "unavailable"** (Neo4j not running or dependencies missing)
```json
{
  "graphiti_status": "unavailable",
  "knowledge_context": null
}
```

**Status: "timeout"** (Graphiti search exceeded timeout)
```json
{
  "graphiti_status": "timeout",
  "knowledge_context": null
}
```

**Status: "error"** (Graphiti search error)
```json
{
  "graphiti_status": "error",
  "knowledge_context": null
}
```

---

### 2. search - Semantic Search with Knowledge Graph

Search documents using semantic, keyword, or hybrid search with optional knowledge graph enrichment.

#### Standard Response

**Parameters:**
- `query` (string) - Search query
- `search_mode` (string, default: "hybrid") - Search mode: "semantic", "keyword", or "hybrid"
- `limit` (number, default: 5) - Maximum results to return
- `include_graph_context` (boolean, default: false) - Enable knowledge graph enrichment

**Response schema (include_graph_context=false):**

```json
{
  "success": true,
  "results": [
    {
      "id": "uuid-1",
      "text": "Full document text content...",
      "score": 0.87,
      "metadata": {
        "filename": "example.pdf",
        "indexed_at": "2026-02-10T10:30:00Z",
        "category": "technical"
      }
    }
  ],
  "count": 1
}
```

**Field descriptions:**
- `success` (boolean) - Always true for successful searches
- `results` (array) - List of matching documents
  - `id` (string) - Document UUID
  - `text` (string) - Full document content
  - `score` (number) - Relevance score (0.0-1.0)
  - `metadata` (object) - Document metadata (varies by document)
- `count` (number) - Number of results returned

**Empty results:**
```json
{
  "success": true,
  "results": [],
  "count": 0
}
```

#### Enriched Response (Knowledge Graph)

**Response schema (include_graph_context=true):**

```json
{
  "success": true,
  "results": [
    {
      "id": "uuid-1",
      "text": "Full document text content...",
      "score": 0.87,
      "metadata": {
        "filename": "example.pdf",
        "indexed_at": "2026-02-10T10:30:00Z",
        "category": "technical"
      },
      "graphiti_context": {
        "entities": [
          {"name": "TechCorp", "type": "Organization"},
          {"name": "Product X", "type": "Product"}
        ],
        "relationships": [
          {
            "source": "TechCorp",
            "target": "Product X",
            "type": "PRODUCES"
          }
        ]
      }
    }
  ],
  "count": 1,
  "graphiti_status": "available",
  "graphiti_coverage": "1/1 documents"
}
```

**Additional enriched fields:**
- `graphiti_status` (string) - Knowledge graph enrichment status (see [Appendix](#graphiti_status-values))
- `graphiti_coverage` (string) - Documents enriched vs total in format `"X/Y documents"`
  - Example: `"3/5 documents"` means 3 out of 5 results have graph enrichment
  - Missing enrichment reasons: document not in graph, Graphiti search failed per-doc
- `results[].graphiti_context` (object|null) - Per-document knowledge graph context
  - `entities` (array) - Entities found in this document
  - `relationships` (array) - Relationships between entities in this document

**Partial enrichment example:**

When some documents have graph context but others don't:

```json
{
  "success": true,
  "results": [
    {
      "id": "uuid-1",
      "text": "...",
      "graphiti_context": {
        "entities": [...],
        "relationships": [...]
      }
    },
    {
      "id": "uuid-2",
      "text": "...",
      "graphiti_context": null  // This document not in knowledge graph
    }
  ],
  "count": 2,
  "graphiti_status": "available",
  "graphiti_coverage": "1/2 documents"
}
```

---

### 3. list_documents - Browse Knowledge Base

List documents in the knowledge base with optional filtering.

**Parameters:**
- `category` (string, optional) - Filter by category
- `limit` (number, default: 10) - Maximum documents to return
- `offset` (number, default: 0) - Pagination offset

**Response schema:**

```json
{
  "success": true,
  "documents": [
    {
      "id": "uuid-1",
      "title": "example.pdf",
      "indexed_at": "2026-02-10T10:30:00Z",
      "category": "technical",
      "size_bytes": 12345
    }
  ],
  "total": 42,
  "returned": 10
}
```

**Field descriptions:**
- `success` (boolean) - Always true for successful queries
- `documents` (array) - List of document metadata
  - `id` (string) - Document UUID
  - `title` (string) - Document title or filename
  - `indexed_at` (string) - ISO 8601 timestamp
  - `category` (string|null) - Document category (if classified)
  - `size_bytes` (number|null) - File size in bytes
- `total` (number) - Total documents matching filter (for pagination)
- `returned` (number) - Number of documents in this response

**Note:** This tool does NOT support knowledge graph enrichment (no `include_graph_context` parameter).

---

### 4. graph_search - Knowledge Graph Relationship Search

Search using knowledge graph relationships to find connected documents.

**Parameters:**
- `query` (string) - Search query (entity names or concepts)
- `limit` (number, default: 5) - Maximum results to return

**Response schema:**

```json
{
  "success": true,
  "results": [
    {
      "id": "uuid-1",
      "title": "example.pdf",
      "score": 0.92,
      "entities": [
        {"name": "TechCorp", "type": "Organization"},
        {"name": "Alice Smith", "type": "Person"}
      ],
      "relationships": [
        {
          "source": "Alice Smith",
          "target": "TechCorp",
          "type": "WORKS_AT"
        }
      ]
    }
  ],
  "count": 1
}
```

**Field descriptions:**
- `success` (boolean) - Always true for successful searches
- `results` (array) - Documents containing matching entities/relationships
  - `id` (string) - Document UUID
  - `title` (string) - Document title or filename
  - `score` (number) - Relevance score based on entity/relationship matches
  - `entities` (array) - Entities found in this document matching query
  - `relationships` (array) - Relationships involving matched entities
- `count` (number) - Number of results returned

**Error response (Neo4j unavailable):**
```json
{
  "success": false,
  "error": "Knowledge graph unavailable: Neo4j connection failed"
}
```

---

### 5. find_related - Find Similar Documents

Find documents related to a specific document by ID.

**Parameters:**
- `document_id` (string) - UUID of the source document
- `limit` (number, default: 5) - Maximum related documents to return

**Response schema:**

```json
{
  "success": true,
  "source_document": {
    "id": "uuid-1",
    "title": "example.pdf"
  },
  "related_documents": [
    {
      "id": "uuid-2",
      "title": "related.pdf",
      "similarity": 0.85,
      "reason": "Shared entities: TechCorp, Product X"
    }
  ],
  "count": 1
}
```

**Field descriptions:**
- `success` (boolean) - Always true for successful queries
- `source_document` (object) - The document we're finding relations for
  - `id` (string) - Source document UUID
  - `title` (string) - Source document title
- `related_documents` (array) - Documents related to the source
  - `id` (string) - Related document UUID
  - `title` (string) - Related document title
  - `similarity` (number) - Similarity score (0.0-1.0)
  - `reason` (string) - Human-readable explanation of relationship
- `count` (number) - Number of related documents found

**Error response (document not found):**
```json
{
  "success": false,
  "error": "Document not found: uuid-123"
}
```

---

### 6. knowledge_summary - Knowledge Graph Summaries

Generate aggregated summaries of knowledge graph entities and relationships by topic, document, entity, or global overview.

**Parameters:**
- `mode` (string) - Operation mode: "topic", "document", "entity", or "overview"
- `query` (string, required for topic mode) - Topic or concept to search for
- `document_id` (string, required for document mode) - UUID of the document to summarize
- `entity_name` (string, required for entity mode) - Entity name to find relationships for
- `limit` (number, default: 100) - Maximum entities/relationships to return

**Response schemas:**

#### Topic Mode

Search for entities and relationships related to a semantic topic.

**Request:**
```json
{
  "mode": "topic",
  "query": "artificial intelligence",
  "limit": 100
}
```

**Response schema:**

```json
{
  "success": true,
  "mode": "topic",
  "query": "artificial intelligence",
  "summary": {
    "entity_count": 15,
    "relationship_count": 42,
    "entity_breakdown": null,
    "top_entities": [
      {
        "name": "Machine Learning",
        "connections": 12,
        "summary": "AI subfield focused on learning from data"
      },
      {
        "name": "Neural Networks",
        "connections": 8,
        "summary": "Computing systems inspired by biological neural networks"
      }
    ],
    "relationship_types": {
      "RELATED_TO": 15,
      "USED_FOR": 12,
      "PART_OF": 8
    },
    "key_insights": [
      "Machine Learning is the most connected entity (12 connections)",
      "Most common relationship type: 'RELATED_TO' (15 instances)",
      "Knowledge graph contains 15 entities across 3 document(s)"
    ],
    "data_quality": "full"
  },
  "message": "Semantic search unavailable, used text matching",
  "response_time": 2.5
}
```

**Field descriptions:**
- `success` (boolean) - Always true for successful queries
- `mode` (string) - Operation mode ("topic")
- `query` (string) - The search query used
- `summary` (object) - Aggregated knowledge graph summary
  - `entity_count` (number) - Total entities found for topic
  - `relationship_count` (number) - Total RELATES_TO relationships
  - `entity_breakdown` (object|null) - Entity type counts (null if all types are ['Entity'])
  - `top_entities` (array) - Most connected entities (up to 10)
    - `name` (string) - Entity name
    - `connections` (number) - Number of relationships
    - `summary` (string) - Entity description
  - `relationship_types` (object) - Relationship type breakdown (top 5 types)
  - `key_insights` (array, optional) - Generated insights (present when entity_count >= 5 and relationship_count >= 3)
  - `data_quality` (string) - Data quality level: "full", "sparse", or "entities_only"
- `message` (string, optional) - Status message (fallback notification, quality note, or empty result explanation)
- `response_time` (number) - Query duration in seconds

**Data quality levels:**
- `"full"`: relationship_count >= entity_count * 0.3 (comprehensive relationship data)
- `"sparse"`: relationship_count > 0 but < 30% (limited relationship data, includes warning message)
- `"entities_only"`: relationship_count == 0 (no relationships, only entity mentions)

**Fallback behavior:**
When semantic search returns zero results or times out (>10s), topic mode automatically falls back to Cypher text matching on entity names and summaries. The `message` field indicates when fallback occurred: "Semantic search unavailable, used text matching"

---

#### Document Mode

Get complete entity and relationship inventory for a specific document.

**Request:**
```json
{
  "mode": "document",
  "document_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response schema:**

```json
{
  "success": true,
  "mode": "document",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "summary": {
    "entity_count": 8,
    "relationship_count": 5,
    "entities": [
      {
        "name": "Dr. Smith",
        "connections": 3,
        "summary": "Research scientist specializing in AI"
      },
      {
        "name": "TechCorp",
        "connections": 2,
        "summary": "Technology company developing AI solutions"
      }
    ],
    "relationships": [
      {
        "source": "Dr. Smith",
        "target": "TechCorp",
        "type": "WORKS_FOR",
        "fact": "Dr. Smith works for TechCorp as a senior researcher"
      }
    ],
    "data_quality": "full"
  },
  "response_time": 1.2
}
```

**Field descriptions:**
- `success` (boolean) - Always true for successful queries
- `mode` (string) - Operation mode ("document")
- `document_id` (string) - Document UUID queried
- `summary` (object) - Document knowledge graph summary
  - `entity_count` (number) - Total entities in document
  - `relationship_count` (number) - Total relationships in document
  - `entities` (array) - All entities found in document
    - `name` (string) - Entity name
    - `connections` (number) - Number of relationships this entity has
    - `summary` (string) - Entity description
  - `relationships` (array) - All relationships within document scope
    - `source` (string) - Source entity name
    - `target` (string) - Target entity name
    - `type` (string) - Relationship type
    - `fact` (string) - Human-readable relationship description
  - `data_quality` (string) - Data quality level
- `response_time` (number) - Query duration in seconds

---

#### Entity Mode

Get relationship map for a specific entity (case-insensitive search).

**Request:**
```json
{
  "mode": "entity",
  "entity_name": "Machine Learning",
  "limit": 50
}
```

**Response schema:**

```json
{
  "success": true,
  "mode": "entity",
  "entity_name": "Machine Learning",
  "summary": {
    "matched_entities": [
      {
        "uuid": "abc-123",
        "name": "Machine Learning",
        "summary": "AI subfield focused on learning from data",
        "group_id": "doc_550e8400-e29b-41d4-a716-446655440000_chunk_1",
        "document_id": "550e8400-e29b-41d4-a716-446655440000",
        "relationship_count": 12
      }
    ],
    "relationship_count": 12,
    "connected_entities": 10,
    "relationship_breakdown": {
      "RELATED_TO": 5,
      "USED_FOR": 3,
      "PART_OF": 2,
      "DEVELOPED_BY": 2
    },
    "top_connections": [
      {
        "name": "Neural Networks",
        "relationship": "RELATED_TO",
        "fact": "Machine Learning uses Neural Networks for pattern recognition"
      }
    ],
    "source_documents": ["550e8400-...", "660e9511-..."],
    "data_quality": "full"
  },
  "response_time": 0.8
}
```

**Field descriptions:**
- `success` (boolean) - Always true for successful queries
- `mode` (string) - Operation mode ("entity")
- `entity_name` (string) - Entity name searched (case-insensitive)
- `summary` (object) - Entity relationship summary
  - `matched_entities` (array) - All entities matching the search (can be multiple if name appears in different documents)
    - `uuid` (string) - Entity UUID
    - `name` (string) - Entity name
    - `summary` (string) - Entity description
    - `group_id` (string) - Entity group identifier
    - `document_id` (string) - Document UUID extracted from group_id
    - `relationship_count` (number) - Number of relationships for this entity
  - `relationship_count` (number) - Total relationships across all matched entities
  - `connected_entities` (number) - Number of unique entities connected to matched entities
  - `relationship_breakdown` (object) - Relationship type counts (aggregated across all matches)
  - `top_connections` (array) - Most significant relationships (up to 10)
    - `name` (string) - Connected entity name
    - `relationship` (string) - Relationship type
    - `fact` (string) - Relationship description
  - `source_documents` (array of strings) - All document UUIDs containing matched entities
  - `data_quality` (string) - Data quality level
- `response_time` (number) - Query duration in seconds

**Note:** When multiple entities share the same name (e.g., "Python" the language vs "Python" the snake in different documents), `matched_entities` returns all matches sorted by relationship_count (most connected first). The `relationship_breakdown` and `top_connections` aggregate data across all matches.

---

#### Overview Mode

Get global knowledge graph statistics (no input required).

**Request:**
```json
{
  "mode": "overview"
}
```

**Response schema:**

```json
{
  "success": true,
  "mode": "overview",
  "summary": {
    "entity_count": 74,
    "relationship_count": 10,
    "document_count": 2,
    "top_entities": [
      {
        "name": "Website",
        "connections": 6
      },
      {
        "name": "Blog",
        "connections": 3
      }
    ],
    "relationship_types": {
      "INCLUDED_IN": 4,
      "HANDLES": 3,
      "MANAGES": 2
    },
    "data_quality": "sparse"
  },
  "message": "Knowledge graph has limited relationship data",
  "response_time": 0.5
}
```

**Field descriptions:**
- `success` (boolean) - Always true for successful queries
- `mode` (string) - Operation mode ("overview")
- `summary` (object) - Global graph statistics
  - `entity_count` (number) - Total entities in knowledge graph
  - `relationship_count` (number) - Total RELATES_TO relationships (excludes MENTIONS)
  - `document_count` (number) - Number of unique documents with knowledge graph data
  - `top_entities` (array) - Most connected entities (up to 10)
    - `name` (string) - Entity name
    - `connections` (number) - Number of relationships
  - `relationship_types` (object) - Relationship type breakdown (top 5 types)
  - `data_quality` (string) - Data quality level
- `message` (string, optional) - Data quality notification (present when quality is "sparse" or "entities_only")
- `response_time` (number) - Query duration in seconds

---

#### Empty Results

When no knowledge graph data is found for a query:

```json
{
  "success": true,
  "mode": "topic",
  "query": "nonexistent topic",
  "summary": {
    "entity_count": 0,
    "relationship_count": 0
  },
  "message": "No knowledge graph entities found for this topic. Documents may not have been processed through Graphiti.",
  "response_time": 1.1
}
```

**Empty result behavior:**
- `success` remains `true` (not a query failure, just no data)
- `summary` contains minimal fields: `entity_count: 0`, `relationship_count: 0`
- `message` field explains why no results (document not processed, topic not found, etc.)
- Mode-specific input fields still present (`query`, `document_id`, `entity_name`)

---

#### Error Response

**Neo4j unavailable:**
```json
{
  "success": false,
  "error": "Knowledge graph unavailable: Neo4j connection failed"
}
```

**Invalid mode:**
```json
{
  "success": false,
  "error": "Invalid mode: 'invalid'. Must be one of: topic, document, entity, overview"
}
```

**Missing required parameter:**
```json
{
  "success": false,
  "error": "Topic mode requires 'query' parameter"
}
```

**Cypher query failure:**
```json
{
  "success": false,
  "error": "Neo4j query failed: <error details>"
}
```

---

### 7. list_entities - Entity Inventory Listing

List all entities in the knowledge graph with pagination and optional filtering. Browse entity inventory without needing specific names or queries.

**Response time:** <1s for 50 entities

**Parameters:**
- `limit` (number, default: 50) - Maximum entities to return (1-100, clamped automatically)
- `offset` (number, default: 0) - Number of entities to skip for pagination (0-10000)
- `sort_by` (string, default: "connections") - Sort mode: "connections", "name", or "created_at"
- `search` (string, optional) - Case-insensitive text search on entity name/summary

#### Success Response

**Request (default):**
```json
{
  "limit": 50,
  "offset": 0,
  "sort_by": "connections"
}
```

**Response schema:**

```json
{
  "success": true,
  "entities": [
    {
      "uuid": "abc-123-def-456",
      "name": "Machine Learning",
      "summary": "AI subfield focused on learning from data",
      "relationship_count": 12,
      "source_documents": ["550e8400-e29b-41d4-a716-446655440000"],
      "created_at": "2026-02-11T10:30:00Z",
      "group_id": "doc_550e8400-e29b-41d4-a716-446655440000_chunk_1",
      "labels": ["Entity"]
    },
    {
      "uuid": "def-456-ghi-789",
      "name": "Neural Networks",
      "summary": "Computing systems inspired by biological neural networks",
      "relationship_count": 8,
      "source_documents": ["550e8400-e29b-41d4-a716-446655440000", "660e9511-f3ac-52e5-b827-557766550111"],
      "created_at": "2026-02-11T11:15:00Z",
      "group_id": "doc_660e9511-f3ac-52e5-b827-557766550111_chunk_3",
      "labels": ["Entity"]
    }
  ],
  "pagination": {
    "total_count": 74,
    "has_more": true,
    "offset": 0,
    "limit": 50,
    "sort_by": "connections",
    "search": null
  },
  "metadata": {
    "graph_density": "normal",
    "message": null
  },
  "response_time": 0.4
}
```

**Field descriptions:**

**Top-level fields:**
- `success` (boolean) - Always true for successful queries
- `entities` (array) - List of entity objects
- `pagination` (object) - Pagination metadata
- `metadata` (object) - Graph state metadata (density, contextual messages)
- `response_time` (number) - Query duration in seconds

**Entity fields:**
- `uuid` (string) - Unique entity identifier (Neo4j UUID)
- `name` (string) - Entity name (e.g., "Machine Learning", "TechCorp")
- `summary` (string|null) - Entity description/summary (can be null if missing)
- `relationship_count` (number) - Number of RELATES_TO relationships (excludes MENTIONS)
- `source_documents` (array) - Document UUIDs where entity appears (extracted from group_id)
- `created_at` (string|null) - ISO 8601 timestamp when entity was created (can be null if serialization fails)
- `group_id` (string|null) - Entity group identifier (e.g., "doc_{uuid}_chunk_{N}")
- `labels` (array) - Neo4j node labels (always ["Entity"] in current production)

**Pagination fields:**
- `total_count` (number) - Total entities matching the query (unfiltered count if no search)
- `has_more` (boolean) - Whether more entities exist beyond current page (`offset + limit < total_count`)
- `offset` (number) - Current pagination offset (echoes request parameter)
- `limit` (number) - Current page size (echoes request parameter, clamped to 1-100)
- `sort_by` (string) - Sort mode used (echoes validated parameter)
- `search` (string|null) - Search text used (null if no search, echoes normalized parameter)

**Metadata fields:**
- `graph_density` (string) - Graph connection state: "empty", "sparse", or "normal"
  - `"empty"` - No entities exist (total_count=0)
  - `"sparse"` - >50% of entities have zero relationships (common with current entity extraction)
  - `"normal"` - ≤50% of entities are isolated, good connectivity
- `message` (string|null) - Contextual help message (present for empty/sparse graphs, null otherwise)
  - Empty graph: "Knowledge graph is empty. Add documents via the frontend to populate entities."
  - Sparse graph: "Sparse graphs are normal with current entity extraction. Relationships improve as more documents are added."
  - Normal graph: null (no message needed)

#### Sort Modes

**Sort by connections (default):**
```json
{
  "sort_by": "connections"
}
```
Returns entities ordered by relationship count (descending), then by name (ascending) as tiebreaker.

**Sort by name:**
```json
{
  "sort_by": "name"
}
```
Returns entities in alphabetical order (case-insensitive).

**Sort by creation date:**
```json
{
  "sort_by": "created_at"
}
```
Returns entities ordered by creation timestamp (newest first).

#### Text Search Filtering

**Request with search:**
```json
{
  "search": "machine learning",
  "limit": 20
}
```

**Response:**
```json
{
  "success": true,
  "entities": [
    {
      "uuid": "abc-123",
      "name": "Machine Learning",
      "summary": "AI subfield focused on learning from data",
      "relationship_count": 12,
      "source_documents": ["550e8400-..."],
      "created_at": "2026-02-11T10:30:00Z",
      "group_id": "doc_550e8400-..._chunk_1",
      "labels": ["Entity"]
    }
  ],
  "pagination": {
    "total_count": 1,
    "has_more": false,
    "offset": 0,
    "limit": 20,
    "sort_by": "connections",
    "search": "machine learning"
  },
  "response_time": 0.3
}
```

**Search behavior:**
- Case-insensitive contains search on entity `name` OR `summary` fields
- Search text normalized: stripped of whitespace, empty strings converted to null
- Non-printable characters removed (security measure)
- Maximum search length: 500 characters (validation error if exceeded)

#### Empty Results

**No entities in graph:**
```json
{
  "success": true,
  "entities": [],
  "pagination": {
    "total_count": 0,
    "has_more": false,
    "offset": 0,
    "limit": 50,
    "sort_by": "connections",
    "search": null
  },
  "metadata": {
    "graph_density": "empty",
    "message": "Knowledge graph is empty. Add documents via the frontend to populate entities."
  },
  "response_time": 0.2
}
```

**Search with no matches:**
```json
{
  "success": true,
  "entities": [],
  "pagination": {
    "total_count": 0,
    "has_more": false,
    "offset": 0,
    "limit": 50,
    "sort_by": "connections",
    "search": "nonexistent entity"
  },
  "metadata": {
    "graph_density": "empty",
    "message": "Knowledge graph is empty. Add documents via the frontend to populate entities."
  },
  "response_time": 0.3
}
```

**Sparse graph (>50% isolated entities):**
```json
{
  "success": true,
  "entities": [
    {
      "uuid": "abc-123",
      "name": "Isolated Entity 1",
      "summary": "Entity with no relationships",
      "relationship_count": 0,
      "source_documents": ["550e8400-e29b-41d4-a716-446655440000"],
      "created_at": "2026-02-11T10:30:00Z",
      "group_id": "doc_550e8400-e29b-41d4-a716-446655440000_chunk_1",
      "labels": ["Entity"]
    },
    {
      "uuid": "def-456",
      "name": "Isolated Entity 2",
      "summary": "Another entity with no relationships",
      "relationship_count": 0,
      "source_documents": ["660e9511-f3ac-52e5-b827-557766550111"],
      "created_at": "2026-02-11T11:15:00Z",
      "group_id": "doc_660e9511-f3ac-52e5-b827-557766550111_chunk_2",
      "labels": ["Entity"]
    }
  ],
  "pagination": {
    "total_count": 74,
    "has_more": true,
    "offset": 0,
    "limit": 2,
    "sort_by": "connections",
    "search": null
  },
  "metadata": {
    "graph_density": "sparse",
    "message": "Sparse graphs are normal with current entity extraction. Relationships improve as more documents are added."
  },
  "response_time": 0.4
}
```

#### Error Responses

**Neo4j unavailable:**
```json
{
  "success": false,
  "error": "Knowledge graph unavailable (Neo4j not connected). Check NEO4J_URI environment variable.",
  "error_type": "connection_error",
  "entities": [],
  "pagination": {
    "total_count": 0,
    "has_more": false,
    "offset": 0,
    "limit": 50,
    "sort_by": "connections",
    "search": null
  }
}
```

**Graphiti dependencies missing:**
```json
{
  "success": false,
  "error": "Graphiti knowledge graph unavailable (dependencies not installed). Please install graphiti-core and neo4j packages.",
  "error_type": "connection_error",
  "entities": [],
  "pagination": {
    "total_count": 0,
    "has_more": false,
    "offset": 0,
    "limit": 50,
    "sort_by": "connections",
    "search": null
  }
}
```

**Invalid sort_by parameter:**
```json
{
  "success": true,
  "entities": [...],
  "pagination": {
    "total_count": 74,
    "has_more": true,
    "offset": 0,
    "limit": 50,
    "sort_by": "connections",
    "search": null
  },
  "response_time": 0.4
}
```
Note: Invalid `sort_by` values gracefully fall back to "connections" (logged as warning).

**Search text too long:**
```json
{
  "success": false,
  "error": "Search text exceeds maximum length (500 characters)",
  "error_type": "validation_error",
  "entities": [],
  "pagination": {
    "total_count": 0,
    "has_more": false,
    "offset": 0,
    "limit": 50,
    "sort_by": "connections",
    "search": "<long search text truncated...>"
  }
}
```

**Query execution error:**
```json
{
  "success": false,
  "error": "Failed to query knowledge graph (Neo4j query error)",
  "error_type": "query_error",
  "entities": [],
  "pagination": {
    "total_count": 0,
    "has_more": false,
    "offset": 0,
    "limit": 50,
    "sort_by": "connections",
    "search": null
  }
}
```

**Unexpected error:**
```json
{
  "success": false,
  "error": "list_entities error: <exception details>",
  "error_type": "unknown",
  "entities": [],
  "pagination": {
    "total_count": 0,
    "has_more": false,
    "offset": 0,
    "limit": 50,
    "sort_by": "connections",
    "search": null
  }
}
```

#### Edge Cases

**Isolated entities (no relationships):**
```json
{
  "uuid": "isolated-123",
  "name": "Rare Concept",
  "summary": "A concept with no discovered relationships",
  "relationship_count": 0,
  "source_documents": ["abc-def-..."],
  "created_at": "2026-02-11T15:00:00Z",
  "group_id": "doc_abc-def-..._chunk_5",
  "labels": ["Entity"]
}
```
Note: Production graph has 82.4% isolated entities (relationship_count = 0).

**Null summary:**
```json
{
  "uuid": "no-summary-456",
  "name": "Entity Name",
  "summary": null,
  "relationship_count": 3,
  "source_documents": ["xyz-789-..."],
  "created_at": "2026-02-11T16:00:00Z",
  "group_id": "doc_xyz-789-..._chunk_2",
  "labels": ["Entity"]
}
```

**Created_at serialization failure:**
```json
{
  "uuid": "bad-timestamp-789",
  "name": "Entity Name",
  "summary": "Entity description",
  "relationship_count": 5,
  "source_documents": ["def-456-..."],
  "created_at": null,
  "group_id": "doc_def-456-..._chunk_1",
  "labels": ["Entity"]
}
```
Note: Malformed Neo4j datetime objects are logged as warnings and returned as null.

**Malformed group_id:**
```json
{
  "uuid": "bad-groupid-101",
  "name": "Entity Name",
  "summary": "Entity description",
  "relationship_count": 2,
  "source_documents": [],
  "created_at": "2026-02-11T17:00:00Z",
  "group_id": "invalid_format",
  "labels": ["Entity"]
}
```
Note: Invalid group_id formats result in empty `source_documents` array (logged as warning).

---

### 8. knowledge_timeline - Chronological Knowledge Graph Timeline

**SPEC-041 Note:** Added in 2026-02-13 as part of temporal data implementation.

Get a chronological timeline of recent knowledge graph updates. Returns relationships ordered by creation time (newest first), without semantic ranking.

**Use case:** "What's new in the knowledge graph?" queries where you want chronological order, not semantic relevance.

#### Success Response

**Parameters:**
- `days_back` (int, optional, default: 7) - How many days to look back (1-365)
- `limit` (int, optional, default: 100) - Maximum relationships to return (1-1000)

**Response schema:**

```json
{
  "success": true,
  "timeline": [
    {
      "source_entity": "Python",
      "target_entity": "Machine Learning",
      "relationship_type": "USED_FOR",
      "fact": "Python is commonly used for ML applications",
      "created_at": "2026-02-13T15:30:00Z",
      "valid_at": "2026-02-10T00:00:00Z",
      "invalid_at": null,
      "expired_at": null,
      "source_documents": ["550e8400-e29b-41d4-a716-446655440000"]
    },
    {
      "source_entity": "TensorFlow",
      "target_entity": "Deep Learning",
      "relationship_type": "ENABLES",
      "fact": "TensorFlow enables deep learning implementations",
      "created_at": "2026-02-13T10:00:00Z",
      "valid_at": null,
      "invalid_at": null,
      "expired_at": null,
      "source_documents": ["660e9511-f3ac-52e5-b827-557766550111"]
    }
  ],
  "count": 2,
  "response_time": 1.5
}
```

**Field descriptions:**

**Top-level fields:**
- `success` (boolean) - Always true for successful queries
- `timeline` (array) - Relationships ordered chronologically (newest first)
- `count` (number) - Number of relationships returned
- `response_time` (number) - Query duration in seconds

**Relationship schema:**
- `source_entity` (string) - Source entity name
- `target_entity` (string) - Target entity name
- `relationship_type` (string) - Relationship type (USED_FOR, ENABLES, etc.)
- `fact` (string) - Natural language description of the relationship
- `created_at` (string) - Ingestion timestamp (ISO 8601 with timezone, never null)
- `valid_at` (string|null) - Event time when fact became valid (may be null)
- `invalid_at` (string|null) - Timestamp when fact was invalidated (typically null)
- `expired_at` (string|null) - Timestamp when fact expired (typically null)
- `source_documents` (array of strings) - UUIDs of documents containing this relationship

**Note on response format:**
- Unlike `knowledge_graph_search`, timeline does **not** include an "entities" key
- Returns relationships only, ordered by `created_at DESC`
- This is a distinct response schema for timeline-specific use cases

#### Usage Examples

**Default (last 7 days):**
```json
{
  "days_back": 7,
  "limit": 100
}
```

**Last 30 days:**
```json
{
  "days_back": 30,
  "limit": 100
}
```

**Last 24 hours, top 50 items:**
```json
{
  "days_back": 1,
  "limit": 50
}
```

#### Empty Results

When no relationships exist in the time window:

```json
{
  "success": true,
  "timeline": [],
  "count": 0,
  "response_time": 0.3
}
```

#### Error Responses

**Neo4j unavailable:**
```json
{
  "success": false,
  "error": "Knowledge graph unavailable (Neo4j not connected). Check NEO4J_URI environment variable.",
  "error_type": "connection_error"
}
```

**days_back out of bounds:**
```json
{
  "success": false,
  "error": "days_back must be between 1 and 365 (got: 400)",
  "error_type": "validation_error"
}
```

**limit out of bounds:**
```json
{
  "success": false,
  "error": "limit must be between 1 and 1000 (got: 2000)",
  "error_type": "validation_error"
}
```

**Cypher query failure:**
```json
{
  "success": false,
  "error": "Timeline query failed: <Neo4j error details>",
  "error_type": "query_error"
}
```

#### Comparison: knowledge_timeline vs knowledge_graph_search

| Feature | `knowledge_timeline` | `knowledge_graph_search` |
|---------|---------------------|-------------------------|
| **Ordering** | Chronological (newest first) | Semantic relevance |
| **Query parameter** | Optional (unranked) | Required (semantic search) |
| **Use case** | "What's new?" | "Find knowledge about X" |
| **Returns entities** | No (relationships only) | Yes (entities + relationships) |
| **Response key** | `timeline` | `entities` + `relationships` |
| **Temporal filtering** | Built-in (days_back) | Optional (created_after, etc.) |

---

### 9. knowledge_graph_search - Knowledge Graph Entity and Relationship Search

**SPEC-041 Note:** As of 2026-02-13, this tool includes temporal metadata fields for all entities and relationships, plus temporal filtering parameters.

Search the Graphiti knowledge graph for entities and their relationships with optional temporal filtering. Returns both entities and relationships matching the semantic query.

#### Success Response

**Parameters:**
- `query` (string, required) - Semantic search query (1-1000 chars)
- `limit` (int, optional) - Maximum results (1-50, default: 10)
- `created_after` (string, optional) - Find knowledge added after this timestamp (ISO 8601 with timezone)
- `created_before` (string, optional) - Find knowledge added before this timestamp (ISO 8601 with timezone)
- `valid_after` (string, optional) - Find facts valid after this event time (ISO 8601 with timezone)
- `include_undated` (boolean, optional, default: true) - Include relationships with null `valid_at` when using `valid_after`

**Response schema:**
```json
{
  "success": true,
  "entities": [
    {
      "name": "Python",
      "type": "ProgrammingLanguage",
      "uuid": "entity-uuid-001",
      "source_documents": ["doc-uuid-001", "doc-uuid-002"],
      "created_at": "2025-01-15T10:00:00Z"
    },
    {
      "name": "Machine Learning",
      "type": null,
      "uuid": "entity-uuid-002",
      "source_documents": ["doc-uuid-002"],
      "created_at": "2025-01-15T10:15:00Z"
    }
  ],
  "relationships": [
    {
      "source_entity": "Python",
      "target_entity": "Machine Learning",
      "relationship_type": "USED_FOR",
      "fact": "Python is commonly used for machine learning applications",
      "created_at": "2025-01-15T10:30:00Z",
      "valid_at": "2025-01-10T00:00:00Z",
      "invalid_at": null,
      "expired_at": null,
      "source_documents": ["doc-uuid-001"]
    }
  ],
  "count": 3,
  "metadata": {
    "query": "Python programming",
    "limit": 10,
    "truncated": false
  },
  "response_time": 1.2
}
```

**Field descriptions:**

**Top-level fields:**
- `success` (boolean) - Always true for successful queries
- `entities` (array) - Unique entities found in search
- `relationships` (array) - Relationships between entities
- `count` (number) - Total entities + relationships returned
- `metadata` (object) - Query metadata
- `response_time` (number) - Query duration in seconds

**Entity schema:**
- `name` (string) - Entity name as extracted by Graphiti LLM
- `type` (string|null) - Entity type (Person, Organization, Concept, etc.) - may be null
- `uuid` (string) - Unique entity identifier
- `source_documents` (array of strings) - UUIDs of documents containing this entity
- `created_at` (string|null) - **[SPEC-041]** Ingestion timestamp (ISO 8601 format with timezone)

**Relationship schema:**
- `source_entity` (string) - Source entity name
- `target_entity` (string) - Target entity name
- `relationship_type` (string) - Relationship type (WORKS_AT, RELATES_TO, etc.)
- `fact` (string) - Natural language description of the relationship
- `created_at` (string|null) - **[SPEC-041]** Ingestion timestamp (ISO 8601 format with timezone)
- `valid_at` (string|null) - **[SPEC-041]** Event time when fact became valid (may be null)
- `invalid_at` (string|null) - **[SPEC-041]** Timestamp when fact was invalidated (typically null)
- `expired_at` (string|null) - **[SPEC-041]** Timestamp when fact expired (typically null)
- `source_documents` (array of strings) - UUIDs of documents containing this relationship

**Temporal field notes (SPEC-041):**
- All temporal fields use ISO 8601 format with timezone (e.g., "2025-01-15T10:30:00Z")
- `created_at` is the most reliable temporal dimension (100% populated in production)
- `valid_at`, `invalid_at`, `expired_at` may be null (60% null `valid_at`, 100% null `invalid_at`/`expired_at` in production as of 2026-02-12)
- Null values are explicitly preserved (not omitted) to distinguish "no data" from "zero timestamp"

**Metadata schema:**
- `query` (string) - Original search query (echoed back)
- `limit` (number) - Effective limit applied
- `truncated` (boolean) - Whether results were truncated to limit

#### Temporal Filtering Examples

**Find knowledge added in last week:**
```json
{
  "query": "machine learning",
  "created_after": "2026-02-06T00:00:00Z",
  "limit": 10
}
```

**Find knowledge added between specific dates:**
```json
{
  "query": "AI research",
  "created_after": "2026-01-01T00:00:00Z",
  "created_before": "2026-01-31T23:59:59Z",
  "limit": 20
}
```

**Find facts valid after a specific event (strict mode):**
```json
{
  "query": "product launches",
  "valid_after": "2025-12-01T00:00:00Z",
  "include_undated": false,
  "limit": 10
}
```

**Temporal filtering validation:**

**Inverted range error:**
```json
{
  "success": false,
  "error": "created_after (2026-02-13T00:00:00Z) must be <= created_before (2026-02-01T00:00:00Z)",
  "error_type": "validation_error",
  "entities": [],
  "relationships": [],
  "count": 0
}
```

**Timezone-naive date error:**
```json
{
  "success": false,
  "error": "created_after must include timezone (e.g., '2026-02-13T00:00:00Z' or '2026-02-13T00:00:00-05:00')",
  "error_type": "validation_error",
  "entities": [],
  "relationships": [],
  "count": 0
}
```

**Invalid ISO 8601 format error:**
```json
{
  "success": false,
  "error": "created_after must be valid ISO 8601 format: Invalid isoformat string: '2026-13-01'",
  "error_type": "validation_error",
  "entities": [],
  "relationships": [],
  "count": 0
}
```

#### Error Response

**Neo4j unavailable:**
```json
{
  "success": false,
  "error": "Knowledge graph unavailable (Neo4j not connected). Check NEO4J_URI environment variable.",
  "error_type": "connection_error",
  "entities": [],
  "relationships": [],
  "count": 0,
  "metadata": {
    "query": "test query",
    "limit": 10,
    "truncated": false
  }
}
```

**Graphiti dependencies missing:**
```json
{
  "success": false,
  "error": "Graphiti knowledge graph unavailable (dependencies not installed). Please install graphiti-core and neo4j packages.",
  "error_type": "connection_error",
  "entities": [],
  "relationships": [],
  "count": 0,
  "metadata": {
    "query": "test query",
    "limit": 10,
    "truncated": false
  }
}
```

**Search timeout:**
```json
{
  "success": false,
  "error": "Knowledge graph search timeout (exceeded 10 seconds)",
  "error_type": "timeout",
  "entities": [],
  "relationships": [],
  "count": 0,
  "metadata": {
    "query": "test query",
    "limit": 10,
    "truncated": false
  }
}
```

#### Edge Cases

**Empty graph:**
```json
{
  "success": true,
  "entities": [],
  "relationships": [],
  "count": 0,
  "metadata": {
    "query": "nonexistent topic",
    "limit": 10,
    "truncated": false
  },
  "response_time": 0.3
}
```

**Null entity type (production reality):**
Entity `type` may be null if Graphiti LLM extraction failed or didn't assign a semantic type:
```json
{
  "name": "Concept Name",
  "type": null,
  "uuid": "entity-uuid-003",
  "source_documents": ["doc-uuid-003"],
  "created_at": "2025-01-15T11:00:00Z"
}
```

**All temporal fields null (sparse temporal data):**
Relationships may have null temporal metadata if not extracted or populated:
```json
{
  "source_entity": "Entity A",
  "target_entity": "Entity B",
  "relationship_type": "RELATES_TO",
  "fact": "A relates to B in some way",
  "created_at": "2025-01-15T12:00:00Z",
  "valid_at": null,
  "invalid_at": null,
  "expired_at": null,
  "source_documents": ["doc-uuid-004"]
}
```

---

## Appendix: Field Reference

### graphiti_status Values

The `graphiti_status` field indicates the result of knowledge graph enrichment attempts.

| Value | Meaning | When It Occurs |
|-------|---------|----------------|
| `"available"` | Enrichment successful | Neo4j is running, documents found in knowledge graph, no errors |
| `"unavailable"` | Enrichment not available | Neo4j not running OR Graphiti dependencies missing OR no documents in knowledge graph |
| `"timeout"` | Enrichment timed out | Graphiti search exceeded timeout (default: 5 seconds) |
| `"error"` | Enrichment error | Graphiti search failed with exception (logged to stderr) |
| `"partial"` | Partial enrichment | Some documents enriched, some failed (future - not yet implemented) |

**Relationship to knowledge_context field:**
- `"available"` → `knowledge_context` is populated with entities/relationships
- `"unavailable"` → `knowledge_context` is null
- `"timeout"` → `knowledge_context` is null
- `"error"` → `knowledge_context` is null
- `"partial"` → `knowledge_context` contains whatever was successfully enriched

**Important:** Enrichment failures are **non-blocking**. Tools always return base results (search results, RAG answers) even if enrichment fails.

---

### knowledge_context Structure

Appears in: `rag_query` (when `include_graph_context=true`)

Aggregates knowledge graph data from all source documents.

**Schema:**
```json
{
  "entities": [
    {
      "name": "Entity Name",
      "type": "Entity Type"
    }
  ],
  "relationships": [
    {
      "source": "Source Entity Name",
      "target": "Target Entity Name",
      "type": "Relationship Type"
    }
  ],
  "entity_count": 5,
  "relationship_count": 3
}
```

**Field types:**
- `entities` (array of objects) - Unique entities across all sources
  - `name` (string) - Entity name as extracted by Graphiti LLM
  - `type` (string) - Entity type (Person, Organization, Concept, Location, Product, etc.)
- `relationships` (array of objects) - All relationships between entities
  - `source` (string) - Source entity name (must match an entity.name)
  - `target` (string) - Target entity name (must match an entity.name)
  - `type` (string) - Relationship type (WORKS_AT, RELATES_TO, PRODUCES, etc.)
- `entity_count` (number) - Total unique entities (same as entities.length)
- `relationship_count` (number) - Total relationships (same as relationships.length)

**Entity deduplication:**
Entities with the same `name` are deduplicated. If two documents both mention "TechCorp", it appears once in the aggregated `knowledge_context`.

**Relationship deduplication:**
Relationships are NOT deduplicated. If two documents both have "Alice WORKS_AT TechCorp", the relationship appears twice.

---

### graphiti_context Structure

Appears in: `rag_query.sources[]`, `search.results[]` (when `include_graph_context=true`)

Per-document knowledge graph context.

**Schema:**
```json
{
  "entities": [
    {
      "name": "Entity Name",
      "type": "Entity Type"
    }
  ],
  "relationships": [
    {
      "source": "Source Entity Name",
      "target": "Target Entity Name",
      "type": "Relationship Type"
    }
  ]
}
```

**Same structure as `knowledge_context` but:**
- Scoped to a single document (not aggregated)
- No `entity_count` or `relationship_count` fields
- Can be `null` if document not in knowledge graph

**When graphiti_context is null:**
- Document was never ingested into knowledge graph
- Document ingestion failed or was skipped
- Graphiti search failed for this specific document (partial enrichment)

---

### graphiti_coverage Format

Appears in: `search` (when `include_graph_context=true`)

String format: `"X/Y documents"`

**Examples:**
- `"5/5 documents"` - All results have knowledge graph enrichment
- `"3/5 documents"` - 3 out of 5 results enriched, 2 missing
- `"0/5 documents"` - No results enriched (all documents not in graph)

**Why coverage can be partial:**
- Not all documents have been ingested into knowledge graph
- Some documents failed Graphiti ingestion (rate limits, errors)
- Some documents have no extractable entities (e.g., very short text)

**Note:** This is currently a string for human readability. Future versions may provide structured format (SPEC-037 P2-001 recommendation).

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.3 | 2026-02-13 | Added temporal filtering parameters to knowledge_graph_search, knowledge_timeline tool schema, and RAG temporal context documentation (SPEC-041 complete) |
| 1.2 | 2026-02-13 | Added knowledge_graph_search schema with temporal fields (SPEC-041 P0) |
| 1.1 | 2026-02-12 | Added list_entities schema (SPEC-040 DOC-001) |
| 1.0 | 2026-02-10 | Initial schema documentation (addresses SPEC-037 P1-001) |

## See Also

- **Implementation:** `mcp_server/txtai_rag_mcp.py`
- **Tests:** `mcp_server/tests/test_txtai_rag_mcp.py`
- **Specification:** `SDD/requirements/SPEC-037-mcp-gap-analysis-v2.md`
- **Setup Guide:** `mcp_server/README.md`
