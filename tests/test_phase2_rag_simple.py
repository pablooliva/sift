"""
Simple test script for Phase 2: RAG Workflow Implementation (SPEC-013)

Tests the rag_query() method using direct API calls.
"""

import requests
import time
import json


class SimpleRAGClient:
    """Simplified client for RAG testing without Streamlit dependencies"""

    def __init__(self, base_url="http://localhost:8300"):
        self.base_url = base_url

    def rag_query(self, question: str, context_limit: int = 5, timeout: int = 30):
        """
        Simplified RAG query implementation for testing.
        Mirrors the api_client.py implementation.
        """
        try:
            # Input validation
            question = question.strip()

            if not question:
                return {"success": False, "error": "empty_question"}

            if len(question) > 1000:
                question = question[:1000]

            # Step 1: Search embeddings
            start_time = time.time()

            search_response = requests.get(
                f"{self.base_url}/search",
                params={"query": question, "limit": context_limit},
                timeout=timeout
            )
            search_response.raise_for_status()
            search_results = search_response.json()

            search_time = time.time() - start_time
            print(f"  → Search took {search_time:.2f}s, found {len(search_results)} results")

            if not search_results or len(search_results) == 0:
                return {
                    "success": True,
                    "answer": "I don't have enough information to answer this question.",
                    "sources": [],
                    "response_time": search_time
                }

            # Step 2: Extract context
            context_parts = []
            source_ids = []

            for result in search_results:
                doc_id = result.get("id", "unknown")
                text = result.get("text", "")

                if text:
                    snippet = text[:500] if len(text) > 500 else text
                    context_parts.append(f"Document {doc_id}:\n{snippet}")
                    source_ids.append(doc_id)

            context = "\n\n".join(context_parts)

            # Step 3: Format prompt
            prompt = f"""Answer the question using ONLY the information provided in the context below.

Context:
{context}

Question: {question}

Instructions:
- Use ONLY the information from the context above
- If the context doesn't contain enough information to answer, respond with "I don't have enough information to answer this question."
- Be concise and factual
- Do not use external knowledge
- Cite specific document IDs when relevant

Answer:"""

            # Step 4: Generate answer with Together AI
            llm_start = time.time()

            import os
            together_api_key = os.getenv("TOGETHERAI_API_KEY")

            if not together_api_key:
                return {"success": False, "error": "missing_api_key"}

            llm_response = requests.post(
                "https://api.together.xyz/v1/completions",
                headers={
                    "Authorization": f"Bearer {together_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "Qwen/Qwen2.5-72B-Instruct-Turbo",
                    "prompt": prompt,
                    "max_tokens": 500,
                    "temperature": 0.3,
                    "top_p": 0.7,
                    "top_k": 50,
                    "repetition_penalty": 1.0,
                    "stop": ["\n\nQuestion:", "\n\nContext:"]
                },
                timeout=timeout - search_time
            )
            llm_response.raise_for_status()

            llm_result = llm_response.json()
            llm_time = time.time() - llm_start
            total_time = time.time() - start_time

            print(f"  → LLM took {llm_time:.2f}s, total {total_time:.2f}s")

            # Parse Together AI response
            if "choices" in llm_result and len(llm_result["choices"]) > 0:
                answer = llm_result["choices"][0].get("text", "").strip()
            else:
                return {"success": False, "error": "invalid_llm_response"}

            answer = answer.strip()

            if not answer or len(answer) < 10:
                return {"success": False, "error": "low_quality_response"}

            return {
                "success": True,
                "answer": answer,
                "sources": source_ids,
                "response_time": total_time,
                "num_documents": len(search_results)
            }

        except requests.exceptions.Timeout:
            return {"success": False, "error": "timeout"}

        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"api_error: {str(e)}"}

        except Exception as e:
            return {"success": False, "error": f"unexpected_error: {str(e)}"}


def main():
    print("\n" + "="*70)
    print("SPEC-013 Phase 2: RAG Workflow Test")
    print("Testing rag_query() with Together AI LLM")
    print("="*70)

    client = SimpleRAGClient()

    # Test 1: Basic query
    print("\n[TEST 1] Basic RAG Query")
    print("-" * 70)

    question = "What documents are in the system?"
    print(f"Question: {question}")

    result = client.rag_query(question, context_limit=5, timeout=30)

    print(f"\nResult:")
    print(f"  Success: {result.get('success')}")

    if result.get('success'):
        print(f"  Answer: {result.get('answer')[:200]}...")
        print(f"  Sources: {result.get('sources', [])[:3]}")
        print(f"  Response time: {result.get('response_time', 0):.2f}s")

        if result.get('response_time', 0) <= 5.0:
            print("  ✓ Performance: Within 5s target")
        else:
            print(f"  ⚠ Performance: Exceeded 5s target")

        print("\n✓ TEST 1 PASSED")
    else:
        print(f"  Error: {result.get('error')}")
        print("\n✗ TEST 1 FAILED")

    # Test 2: Empty question
    print("\n[TEST 2] Empty Question Validation")
    print("-" * 70)

    result = client.rag_query("", context_limit=5, timeout=30)

    if not result.get('success') and result.get('error') == 'empty_question':
        print("✓ TEST 2 PASSED: Empty question correctly rejected")
    else:
        print("✗ TEST 2 FAILED")

    # Test 3: Performance test
    print("\n[TEST 3] Performance Test (3 queries)")
    print("-" * 70)

    questions = [
        "What files are in the system?",
        "Are there any documents?",
        "What content is available?"
    ]

    times = []

    for i, q in enumerate(questions, 1):
        print(f"\n  Query {i}: {q}")
        start = time.time()
        result = client.rag_query(q, context_limit=5, timeout=30)
        elapsed = time.time() - start

        if result.get('success'):
            times.append(result.get('response_time', elapsed))
            print(f"  ✓ Success in {result.get('response_time', elapsed):.2f}s")
        else:
            print(f"  ✗ Failed: {result.get('error')}")

    if times:
        avg = sum(times) / len(times)
        print(f"\n  Average response time: {avg:.2f}s")

        if avg <= 5.0:
            print("  ✓ TEST 3 PASSED: Performance within target")
        else:
            print(f"  ⚠ TEST 3 WARNING: Average exceeds 5s target")
    else:
        print("  ✗ TEST 3 FAILED: No successful queries")

    print("\n" + "="*70)
    print("Testing complete!")
    print("="*70)


if __name__ == "__main__":
    main()
