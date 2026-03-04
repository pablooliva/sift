#!/usr/bin/env python3
"""
Test ollama-labels workflow classification accuracy.
SPEC-019 Phase 1 validation.
"""

import requests
import json

# Test cases with expected categories
test_cases = [
    ("API documentation for REST endpoints explaining how to authenticate", "reference"),
    ("Analysis of performance bottlenecks in the database query optimizer", "analysis"),
    ("Source code: class BinarySearchTree { def insert(self, val): ... }", "technical"),
    ("Product roadmap for Q1 2025 with key strategic initiatives", "strategic"),
    ("Meeting notes from sprint planning with action items", "meeting-notes"),
    ("TODO: Fix critical bug in payment processing before release", "actionable"),
    ("Weekly status update: Completed 80% of planned features", "status"),
]

API_URL = "http://localhost:8300"

def test_classification():
    """Test classification accuracy via workflow."""
    correct = 0
    total = len(test_cases)

    print("Testing ollama-labels workflow classification...")
    print("=" * 60)

    for text, expected in test_cases:
        try:
            response = requests.post(
                f"{API_URL}/workflow",
                json={"name": "ollama-labels", "elements": [text]},
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            predicted = result[0] if result else "unknown"

            is_correct = predicted == expected
            if is_correct:
                correct += 1
                status = "✓"
            else:
                status = "✗"

            print(f"{status} Expected: {expected:15s} Got: {predicted:15s}")
            print(f"  Text: {text[:60]}...")

        except Exception as e:
            print(f"✗ ERROR: {e}")
            print(f"  Text: {text[:60]}...")

    print("=" * 60)
    accuracy = (correct / total) * 100
    print(f"Accuracy: {correct}/{total} ({accuracy:.1f}%)")

    if accuracy >= 95:
        print("✓ PASS: Accuracy meets ≥95% requirement (SPEC-019 REQ-002)")
        return True
    else:
        print("✗ FAIL: Accuracy below 95% requirement")
        return False

if __name__ == "__main__":
    success = test_classification()
    exit(0 if success else 1)
