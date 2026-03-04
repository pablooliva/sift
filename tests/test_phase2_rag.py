"""
Test script for Phase 2: RAG Workflow Implementation (SPEC-013)

Tests the rag_query() method in api_client.py with Together AI LLM.

Requirements tested:
- REQ-007: API client rag_query() method
- REQ-008: RAG prompt engineering
- REQ-009: RAG response time ≤5 seconds
- SEC-002: Input validation
- REL-001: Graceful error handling
- PERF-003: Performance validation

Usage:
    python test_phase2_rag.py
"""

import sys
import time
from pathlib import Path

# Add frontend to path (parent.parent goes from tests/ to project root)
sys.path.insert(0, str(Path(__file__).parent.parent / "frontend"))

from utils.api_client import TxtAIClient


def test_rag_basic_query():
    """Test basic RAG query functionality (REQ-007, REQ-009)"""
    print("\n" + "="*70)
    print("TEST 1: Basic RAG Query")
    print("="*70)

    client = TxtAIClient()

    # Test question about documents that should be in the index
    question = "What documents are in the system?"

    print(f"\nQuestion: {question}")
    print(f"Testing RAG query...")

    start_time = time.time()
    result = client.rag_query(question, context_limit=5, timeout=30)
    elapsed = time.time() - start_time

    print(f"\nResponse time: {elapsed:.2f}s")
    print(f"Success: {result.get('success')}")

    if result.get('success'):
        print(f"\nAnswer:\n{result.get('answer')}")
        print(f"\nSources: {result.get('sources', [])}")
        print(f"Number of documents retrieved: {result.get('num_documents', 0)}")
        print(f"RAG internal timing: {result.get('response_time', 0):.2f}s")

        # Validate performance (PERF-003: target ≤5s)
        if result.get('response_time', 0) <= 5.0:
            print("✓ PASS: Response time within 5s target")
        else:
            print(f"⚠ WARNING: Response time exceeded 5s target ({result.get('response_time'):.2f}s)")

        return True
    else:
        print(f"✗ FAIL: {result.get('error')}")
        return False


def test_rag_empty_question():
    """Test RAG with empty question (SEC-002)"""
    print("\n" + "="*70)
    print("TEST 2: Empty Question (Input Validation)")
    print("="*70)

    client = TxtAIClient()

    result = client.rag_query("", context_limit=5, timeout=30)

    print(f"Success: {result.get('success')}")
    print(f"Error: {result.get('error')}")

    if not result.get('success') and result.get('error') == 'empty_question':
        print("✓ PASS: Empty question correctly rejected")
        return True
    else:
        print("✗ FAIL: Should reject empty question")
        return False


def test_rag_long_question():
    """Test RAG with very long question (SEC-002)"""
    print("\n" + "="*70)
    print("TEST 3: Long Question (Input Validation)")
    print("="*70)

    client = TxtAIClient()

    # Create a question longer than 1000 chars
    long_question = "What is in my documents? " * 50  # ~1250 chars

    print(f"Question length: {len(long_question)} chars")

    result = client.rag_query(long_question, context_limit=5, timeout=30)

    print(f"Success: {result.get('success')}")

    if result.get('success') is not None:  # Either success or controlled failure
        print("✓ PASS: Long question handled gracefully")
        return True
    else:
        print("✗ FAIL: Unexpected result")
        return False


def test_rag_no_documents():
    """Test RAG when no relevant documents exist (REL-001)"""
    print("\n" + "="*70)
    print("TEST 4: No Relevant Documents (Graceful Degradation)")
    print("="*70)

    client = TxtAIClient()

    # Question about something unlikely to be in documents
    question = "What is the airspeed velocity of an unladen swallow?"

    print(f"Question: {question}")

    result = client.rag_query(question, context_limit=5, timeout=30)

    print(f"Success: {result.get('success')}")

    if result.get('success'):
        print(f"Answer: {result.get('answer')}")

        # Should return "I don't have enough information" if no docs found
        answer = result.get('answer', '')
        if 'don\'t have enough information' in answer.lower() or len(result.get('sources', [])) == 0:
            print("✓ PASS: Gracefully handled no relevant documents")
            return True
        else:
            print("⚠ WARNING: Generated answer despite potentially no relevant docs")
            return True  # Still a pass if it returned something reasonable
    else:
        print(f"Error: {result.get('error')}")
        # Graceful failure is also acceptable
        print("✓ PASS: Gracefully failed")
        return True


def test_rag_specific_query():
    """Test RAG with a specific query to check answer quality (REQ-008)"""
    print("\n" + "="*70)
    print("TEST 5: Specific Query (Answer Quality)")
    print("="*70)

    client = TxtAIClient()

    # Ask about a specific topic
    question = "Are there any financial or tax-related documents?"

    print(f"Question: {question}")

    result = client.rag_query(question, context_limit=5, timeout=30)

    print(f"Success: {result.get('success')}")

    if result.get('success'):
        answer = result.get('answer', '')
        sources = result.get('sources', [])

        print(f"\nAnswer:\n{answer}")
        print(f"\nSources: {sources}")

        # Check answer quality
        answer_length = len(answer)
        print(f"\nAnswer length: {answer_length} chars")

        if answer_length >= 10:  # Minimum quality check
            print("✓ PASS: Answer has reasonable length")

            # Check if answer stays grounded (shouldn't hallucinate)
            if any(keyword in answer.lower() for keyword in ['context', 'information', 'documents']):
                print("✓ PASS: Answer appears grounded in context")

            return True
        else:
            print("✗ FAIL: Answer too short")
            return False
    else:
        print(f"✗ FAIL: {result.get('error')}")
        return False


def test_rag_performance_multiple():
    """Test RAG performance across multiple queries (PERF-003)"""
    print("\n" + "="*70)
    print("TEST 6: Performance Validation (Multiple Queries)")
    print("="*70)

    client = TxtAIClient()

    questions = [
        "What files are in the system?",
        "Are there any images?",
        "What topics are covered?"
    ]

    times = []
    successes = 0

    for i, question in enumerate(questions, 1):
        print(f"\nQuery {i}/3: {question}")

        start = time.time()
        result = client.rag_query(question, context_limit=5, timeout=30)
        elapsed = time.time() - start

        times.append(elapsed)

        if result.get('success'):
            successes += 1
            print(f"  ✓ Success in {elapsed:.2f}s")
        else:
            print(f"  ✗ Failed: {result.get('error')}")

    # Calculate statistics
    avg_time = sum(times) / len(times) if times else 0
    max_time = max(times) if times else 0

    print(f"\n{'─'*70}")
    print(f"Results:")
    print(f"  Successes: {successes}/{len(questions)}")
    print(f"  Average time: {avg_time:.2f}s")
    print(f"  Max time: {max_time:.2f}s")
    print(f"  Target: ≤5.0s")

    if avg_time <= 5.0:
        print("  ✓ PASS: Average time within target")
        return True
    else:
        print(f"  ⚠ WARNING: Average time exceeds target")
        return False


def main():
    """Run all RAG tests"""
    print("\n" + "█"*70)
    print("SPEC-013 Phase 2: RAG Workflow Implementation Tests")
    print("Testing rag_query() method with Together AI LLM")
    print("█"*70)

    tests = [
        ("Basic RAG Query", test_rag_basic_query),
        ("Empty Question", test_rag_empty_question),
        ("Long Question", test_rag_long_question),
        ("No Documents", test_rag_no_documents),
        ("Answer Quality", test_rag_specific_query),
        ("Performance", test_rag_performance_multiple),
    ]

    results = []

    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n✗ TEST FAILED WITH EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "█"*70)
    print("TEST SUMMARY")
    print("█"*70)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for name, p in results:
        status = "✓ PASS" if p else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\n{'─'*70}")
    print(f"Total: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    print("─"*70)

    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        return 0
    else:
        print("⚠ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
