# txtai's 3 Search Types

txtai Search Types Summary

1. Semantic Search (Dense Vectors) - What you currently have

- Uses embeddings to find semantically similar content
- Scores: 0-1 range
- Best for: Natural language queries, conceptual matching
- Example: "coco" matches documents about chocolate, coconut, etc.

2. Keyword Search (Sparse Vectors/BM25)

- Traditional keyword matching (like Google)
- Finds exact term matches
- Fast for specific keywords
- Example: "coco" only matches documents containing "coco"

3. Hybrid Search - Recommended for your use case

- Combines both semantic AND keyword search
- Best of both worlds: exact matches + semantic similarity
- Example: "coco" finds exact "coco" matches first, plus related content

---
How to Enable Hybrid Search

Based on the txtai documentation, here's what you'd need to add to your config.yml:

embeddings:
path: sentence-transformers/all-MiniLM-L6-v2
content: postgresql+psycopg2://postgres:postgres@postgres:5432/txtai
backend: qdrant_txtai.ann.qdrant
hybrid: true  # ← Add this to enable hybrid search
qdrant:
    host: qdrant
    port: 6333
    collection: txtai_embeddings

However, there's a potential compatibility issue: I'm not certain if the Qdrant backend supports hybrid search, as most examples use
FAISS. You may need to test this or switch backends.

Would you like me to:
1. Test enabling hybrid search with your current Qdrant setup?
2. Research Qdrant + hybrid search compatibility first?
3. Look into switching to a different backend that definitely supports hybrid search?

Sources:
- https://github.com/neuml/txtai
- https://github.com/neuml/txtai/blob/master/examples/48_Benefits_of_hybrid_search.ipynb
- https://neuml.github.io/txtai/embeddings/configuration/
- https://neuml.hashnode.dev/whats-new-in-txtai-60