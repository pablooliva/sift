#!/usr/bin/env python3
"""
Simple test for Ollama classification integration (SPEC-019 Phase 1)
Tests Ollama API directly without frontend dependencies
"""
import requests
import os
import re

# Configuration
OLLAMA_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_MODEL = "llama3.2-vision:11b"
LABELS = ["reference", "analysis", "technical", "strategic", "meeting-notes", "actionable", "status"]

# Test documents
test_docs = [
    {
        "text": """# API Authentication Guide
This guide explains how to authenticate with the REST API using OAuth 2.0.
Follow these steps to obtain an access token and make authenticated requests.""",
        "expected": "reference"
    },
    {
        "text": """After analyzing the performance metrics, I found that the database query
latency increased by 300% after the last deployment. The root cause appears
to be missing indexes on the user_sessions table.""",
        "expected": "analysis"
    },
    {
        "text": """// Implementation of binary search tree
class BSTNode {
    constructor(value) {
        this.value = value;
        this.left = null;
        this.right = null;
    }
}""",
        "expected": "technical"
    },
    {
        "text": """Q4 Product Roadmap:
- Launch mobile app (January)
- Implement real-time sync (February)
- Add analytics dashboard (March)""",
        "expected": "strategic"
    },
    {
        "text": """Meeting Notes - Sprint Planning 2024-12-09
Attendees: Alice, Bob, Carol
- Discussed upcoming feature priorities
- Agreed to focus on performance improvements""",
        "expected": "meeting-notes"
    },
    {
        "text": """TODO: Review pull request #456 by EOD
URGENT: Fix production bug in payment processing
Follow up with customer support about ticket #789""",
        "expected": "actionable"
    },
    {
        "text": """Weekly Status Update - Week of Dec 9
Completed: API endpoint refactoring, Database migration scripts
In Progress: Frontend redesign (60% complete)""",
        "expected": "status"
    }
]

def classify_with_ollama(text, labels):
    """Classify text using Ollama"""
    prompt = f"""Classify this document into exactly ONE category. Choose the single best match.

Categories and their meanings:
- reference: Guides, specifications, documentation, APIs, how-to articles (things you look up for information)
- analysis: Research findings, investigations, root cause analysis, performance analysis (your thinking and conclusions)
- technical: Source code, infrastructure configuration, implementation details, architecture diagrams
- strategic: Product roadmaps, business plans, vision documents, long-term goals, strategic initiatives
- meeting-notes: Records of meetings, discussions, attendees, decisions made in meetings
- actionable: TODOs, tasks, urgent items, follow-ups, action items requiring immediate attention
- status: Progress reports, status updates, completion percentages, current state of work

Document to classify:
\"\"\"
{text}
\"\"\"

Think step by step:
1. What is the primary purpose of this document?
2. Who would use this document and why?
3. Which category best matches that purpose?

Respond with ONLY the category name (one word).
Category:"""

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9
                }
            },
            timeout=45
        )
        response.raise_for_status()

        result = response.json()
        llm_response = result.get("response", "").strip()

        # Extract category from response
        category = None

        # Method 1: Exact match
        for label in labels:
            if llm_response.lower() == label.lower():
                category = label
                break

        # Method 2: Find label in words
        if not category:
            words = re.findall(r'\b\w+(?:-\w+)*\b', llm_response.lower())
            for word in words:
                for label in labels:
                    if word == label.lower():
                        category = label
                        break
                if category:
                    break

        # Method 3: Default to first label
        if not category:
            print(f"    Warning: Could not extract category from: '{llm_response}'")
            category = labels[0]

        return {"success": True, "category": category, "raw_response": llm_response}

    except Exception as e:
        return {"success": False, "error": str(e)}

def main():
    print("=" * 80)
    print("Testing Ollama Classification (SPEC-019 Phase 1)")
    print("=" * 80)
    print(f"Ollama URL: {OLLAMA_URL}")
    print(f"Model: {OLLAMA_MODEL}")
    print()

    # Test Ollama availability
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        response.raise_for_status()
        print("✓ Ollama is accessible")
    except Exception as e:
        print(f"✗ Cannot connect to Ollama: {e}")
        return 1

    print()

    # Run tests
    results = []
    for i, doc in enumerate(test_docs, 1):
        print(f"Test {i}/{len(test_docs)}: {doc['expected']}")
        print(f"  Text: {doc['text'][:60].strip()}...")

        result = classify_with_ollama(doc["text"], LABELS)

        if result["success"]:
            predicted = result["category"]
            correct = predicted == doc["expected"]

            results.append({
                "test": i,
                "expected": doc["expected"],
                "predicted": predicted,
                "correct": correct,
                "raw_response": result["raw_response"]
            })

            status = "✓" if correct else "✗"
            print(f"  {status} Predicted: {predicted}")
            if not correct:
                print(f"    Expected: {doc['expected']}")
                print(f"    Raw response: '{result['raw_response']}'")
        else:
            print(f"  ✗ Classification failed: {result.get('error')}")
            results.append({
                "test": i,
                "expected": doc["expected"],
                "predicted": None,
                "correct": False,
                "error": result.get("error")
            })

        print()

    # Summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)

    correct_count = sum(1 for r in results if r["correct"])
    total_count = len(results)
    accuracy = (correct_count / total_count) * 100 if total_count > 0 else 0

    print(f"Accuracy: {correct_count}/{total_count} ({accuracy:.1f}%)")
    print()

    # Show failures
    failures = [r for r in results if not r["correct"]]
    if failures:
        print("Failures:")
        for f in failures:
            if "error" in f:
                print(f"  Test {f['test']}: {f['expected']} - Error: {f['error']}")
            else:
                print(f"  Test {f['test']}: Expected '{f['expected']}' but got '{f['predicted']}'")
                if 'raw_response' in f:
                    print(f"    Raw LLM response: '{f['raw_response']}'")
    else:
        print("✓ All tests passed!")

    print()

    # Check against SPEC-019 requirement (≥95% accuracy)
    if accuracy >= 95.0:
        print(f"✓ PASS: Meets SPEC-019 requirement (≥95% accuracy)")
        return 0
    else:
        print(f"✗ FAIL: Below SPEC-019 requirement (need ≥95%, got {accuracy:.1f}%)")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
