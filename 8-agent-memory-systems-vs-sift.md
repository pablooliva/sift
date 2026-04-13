# How This Stack Compares to 8 Agent Memory Systems

A recent [survey of agent memory systems](https://synix.dev/articles/agent-memory-systems/) reviewed Mem0, Letta, Cognee, Graphiti, Hindsight, EverMemOS, Tacnode, and Hyperspell. Here's how they compare to the stack implemented in this project (txtai + Graphiti/Neo4j + PostgreSQL + Qdrant).

## Systems This Project Already Covers

**Graphiti** — This project uses Graphiti for its knowledge graph layer, and the article confirms it has "the most thoughtful data model of the eight systems." Its bi-temporal edges, two-phase entity deduplication, and contradiction detection are core strengths. The article's main critique (high LLM cost per episode) is valid but manageable at personal-knowledge scale vs. high-volume production.

**Cognee** — Cognee targets a similar space but has notable weaknesses: no deduplication across documents, string-based entity matching that creates duplicates, and zero temporal model. Graphiti addresses all of these.

**Letta (MemGPT)** — Letta offers PostgreSQL ACID guarantees and memory_rethink consolidation, but lacks entity deduplication and contradiction detection — capabilities Graphiti already provides in this stack.

## Worth Knowing About

**Hindsight** — The most interesting system not used in this project. Key capabilities beyond the current stack:

1. **Four parallel retrieval fusion** (semantic + BM25 + graph traversal with spreading activation + temporal) merged via Reciprocal Rank Fusion. This project already does hybrid search (semantic + BM25), but Hindsight's spreading activation on the graph is a different approach — it simulates how associations propagate through a network rather than doing direct traversal. This could surface non-obvious connections that standard graph queries miss.
2. **Typed facts with confidence** — opinions get stored with confidence scores that can decay or strengthen, adding a metadata layer for belief tracking.
3. **Causal link tracking** — fact A led to fact B. Graphiti tracks temporal edges but not explicit causality chains.
4. **Single PostgreSQL + pgvector** — achieves sophisticated retrieval without Neo4j. The architectural lesson is that spreading-activation-style retrieval could potentially complement this project's existing search paths.

Hindsight's spreading activation retrieval and confidence-scored opinions are genuinely novel patterns that could inform future enhancements.

## Less Relevant Alternatives

**Mem0** — Too simple. No temporal model, overwrites without versioning. This project's stack exceeds it in every dimension.

**EverMemOS** — Interesting taxonomy (7 memory types) but requires MongoDB + Elasticsearch + Milvus + Redis with consistency gaps between them. The episode boundary detection idea (using LLM to detect topic shifts) is conceptually interesting but more relevant for chatbot memory than a knowledge base.

**Tacnode** — A database-level infrastructure play (ACID across structured + vector + JSON). Closed-source. The time-travel queries concept is appealing but Graphiti's bi-temporal model already covers this semantically.

**Hyperspell** — Solves OAuth data access across 43 services. Useful if you need unified search across Gmail + Slack + Notion simultaneously, but this project handles data ingestion through its own upload pipeline and integrations.

## Bottom Line

This project's txtai + Graphiti stack already covers the strongest patterns in the agent memory space. The one genuinely additive idea is Hindsight's spreading activation retrieval — it would complement existing graph traversal by surfacing second and third-degree associations that direct Cypher queries miss. If there's a next enhancement to pursue, that's where to look.
