#!/usr/bin/env python3
"""
Test script for SPEC-019 Phase 3: Embeddings Migration to Ollama.

Tests:
1. Document indexing with Ollama embeddings
2. Semantic search functionality
3. Hybrid search (semantic + keyword)
4. Search quality comparison

Requirements:
- txtai API running with custom_actions.ollama_embeddings.transform
- Ollama running with mxbai-embed-large model
- Database reset (empty index)
"""

import requests
import time
import json
import os

API_URL = os.environ.get("TXTAI_API_URL", "http://localhost:9301")

# Test documents covering different domains
TEST_DOCUMENTS = [
    {
        "id": "doc1",
        "text": "Machine learning is a subset of artificial intelligence that enables computers to learn from data without explicit programming. Deep learning uses neural networks with multiple layers."
    },
    {
        "id": "doc2",
        "text": "Python is a high-level programming language known for its simplicity and readability. It's widely used in web development, data science, and automation."
    },
    {
        "id": "doc3",
        "text": "The solar system consists of the Sun and eight planets. Earth is the third planet from the Sun and the only known planet with liquid water."
    },
    {
        "id": "doc4",
        "text": "Recipe for chocolate chip cookies: Mix butter, sugar, eggs, vanilla, flour, and chocolate chips. Bake at 350°F for 12 minutes."
    },
    {
        "id": "doc5",
        "text": "Neural networks are computational models inspired by the human brain. They consist of interconnected nodes organized in layers that process information."
    }
]

# Test queries to validate search quality
TEST_QUERIES = [
    {
        "query": "AI and neural networks",
        "expected_docs": ["doc1", "doc5"],  # Should match ML/AI content
        "description": "Semantic search for AI concepts"
    },
    {
        "query": "programming languages",
        "expected_docs": ["doc2"],  # Should match Python content
        "description": "Semantic search for programming"
    },
    {
        "query": "planets",
        "expected_docs": ["doc3"],  # Should match solar system content
        "description": "Keyword search for planets"
    },
    {
        "query": "deep learning layers",
        "expected_docs": ["doc1", "doc5"],  # Both mention layers/neural networks
        "description": "Hybrid search (semantic + keyword)"
    }
]


def print_step(step_num, description):
    """Print test step header."""
    print(f"\n{'='*60}")
    print(f"Step {step_num}: {description}")
    print('='*60)


def add_documents():
    """Add test documents to the index."""
    print_step(1, "Adding test documents")

    response = requests.post(f"{API_URL}/add", json=TEST_DOCUMENTS)
    response.raise_for_status()

    print(f"✓ Added {len(TEST_DOCUMENTS)} documents")
    for doc in TEST_DOCUMENTS:
        print(f"  - {doc['id']}: {doc['text'][:60]}...")


def index_documents():
    """Build the index (generate embeddings)."""
    print_step(2, "Building index (generating Ollama embeddings)")

    start_time = time.time()
    response = requests.get(f"{API_URL}/index")
    response.raise_for_status()
    elapsed = time.time() - start_time

    print(f"✓ Index built successfully in {elapsed:.2f}s")
    print(f"  - Average: {elapsed/len(TEST_DOCUMENTS):.2f}s per document")

    return elapsed


def verify_count():
    """Verify document count."""
    print_step(3, "Verifying document count")

    response = requests.get(f"{API_URL}/count")
    response.raise_for_status()
    count = response.json()

    expected = len(TEST_DOCUMENTS)
    if count == expected:
        print(f"✓ Document count: {count} (correct)")
    else:
        print(f"✗ Document count: {count} (expected {expected})")
        raise ValueError(f"Count mismatch: got {count}, expected {expected}")


def run_search(query_info):
    """Run a single search query (helper function, not a pytest test)."""
    query = query_info["query"]
    expected = query_info["expected_docs"]
    description = query_info["description"]

    print(f"\nQuery: '{query}'")
    print(f"Type: {description}")

    # Perform search
    response = requests.get(f"{API_URL}/search", params={"query": query, "limit": 3})
    response.raise_for_status()
    results = response.json()

    # Extract result IDs
    result_ids = [r["id"] for r in results]

    # Check if expected docs are in top results
    found = [doc_id for doc_id in expected if doc_id in result_ids]

    print(f"Results: {result_ids}")
    print(f"Expected: {expected}")

    if len(found) > 0:
        print(f"✓ Found {len(found)}/{len(expected)} expected documents")
        for i, result in enumerate(results[:3], 1):
            match = "✓" if result["id"] in expected else " "
            print(f"  {match} #{i}: {result['id']} (score: {result['score']:.3f})")
        return True
    else:
        print(f"✗ No expected documents found in top results")
        return False


def test_all_searches():
    """Test all search queries."""
    print_step(4, "Testing search quality")

    passed = 0
    total = len(TEST_QUERIES)

    for i, query_info in enumerate(TEST_QUERIES, 1):
        print(f"\n--- Test {i}/{total} ---")
        if run_search(query_info):
            passed += 1

    print(f"\n{'='*60}")
    print(f"Search Quality Results: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    print('='*60)

    return passed, total


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("SPEC-019 Phase 3: Embeddings Migration Test")
    print("Testing Ollama mxbai-embed-large embeddings")
    print("="*60)

    try:
        # Step 1: Add documents
        add_documents()

        # Step 2: Build index (generate embeddings)
        index_time = index_documents()

        # Step 3: Verify count
        verify_count()

        # Step 4: Test search quality
        passed, total = test_all_searches()

        # Summary
        print("\n" + "="*60)
        print("PHASE 3 TEST SUMMARY")
        print("="*60)
        print(f"✓ Embeddings generation: WORKING")
        print(f"✓ Index building: {index_time:.2f}s for {len(TEST_DOCUMENTS)} docs")
        print(f"✓ Search quality: {passed}/{total} tests passed ({passed/total*100:.0f}%)")

        if passed == total:
            print("\n✅ ALL TESTS PASSED - Phase 3 embeddings working correctly!")
        elif passed >= total * 0.8:
            print(f"\n⚠️  MOSTLY PASSED - {passed}/{total} tests passed (acceptable)")
        else:
            print(f"\n❌ TESTS FAILED - Only {passed}/{total} tests passed")

        print("="*60)

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
